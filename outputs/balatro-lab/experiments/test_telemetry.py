import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cli'))
from telemetry import extract

class TelemetryTests(unittest.TestCase):
    def test_delayed_coupon_and_edition_update_one_offer(self):
        s={'state':'SHOP','money':10,'round_num':1,'shop':{'cards':[
            {'id':7,'key':'j_test','cost':{'buy':6},'modifier':{}}]}}
        free=copy.deepcopy(s);free['shop']['cards'][0].update(cost={'buy':0},modifier={'edition':'HOLO'})
        after=copy.deepcopy(free);after['shop']['cards']=[]
        d=extract(1,[{'method':'cash_out','result':s},{'method':'gamestate','result':free},
                     {'method':'gamestate','result':free},{'method':'buy','params':{'card':0},'result':after}],{})
        self.assertEqual(len(d['offers']),1)
        o=d['offers'][0]
        self.assertEqual((o['first_seen_price'],o['latest_price'],o['selected_price']),(6,0,0))
        self.assertEqual(len(o['observations']),2)
        self.assertEqual(o['selected_modifier'],{'edition':'HOLO'})
        self.assertEqual(o['selected_line'],4)
    def test_reads_and_purchases_do_not_inflate_offers(self):
        card={'id':7,'key':'j_test','cost':{'buy':4},'modifier':{}}
        s={'state':'SHOP','money':10,'ante_num':1,'round_num':1,'shop':{'cards':[card]},'round':{}}
        empty=copy.deepcopy(s);empty['shop']['cards']=[];empty['money']=6
        reroll=copy.deepcopy(s);reroll['shop']['cards'][0]['id']=8;reroll['money']=1
        rows=[{'method':'cash_out','result':s},{'method':'gamestate','result':s},
              {'method':'buy','params':{'card':0},'result':empty},
              {'method':'reroll','result':reroll},{'method':'gamestate','result':reroll}]
        d=extract(1,rows,{'j_test':{'category':'Joker','rarity':2}})
        self.assertEqual(len(d['offers']),2)
        self.assertEqual(d['offers'][0]['selected_line'],3)
        self.assertEqual(d['summary']['rarity_rates'],{'2':1})
        self.assertEqual([a['money_delta'] for a in d['actions']],[None,-4,-5])
    def test_pack_choices_count_once_and_separate_from_shop(self):
        s={'state':'SMODS_BOOSTER_OPENED','money':0,'round_num':1,'pack':{'cards':[{'id':1,'key':'j_a'},{'id':2,'key':'j_b'}]}}
        after=copy.deepcopy(s);after['pack']['cards']=after['pack']['cards'][1:]
        d=extract(1,[{'method':'buy','result':s},{'method':'pack','params':{'card':0},'result':after},{'method':'gamestate','result':after}],{'j_a':{'category':'Joker','rarity':3},'j_b':{'category':'Joker','rarity':1}})
        self.assertEqual(len(d['offers']),2)
        self.assertEqual(d['summary']['ordinary_shop_joker_offers'],0)
        self.assertEqual(d['summary']['pack_contents_observed'],2)
        self.assertEqual(d['offers'][0]['selected_method'],'pack')
    def test_final_failure_and_menu_do_not_become_win(self):
        d=extract(1,[{'method':'play','result':{'state':'GAME_OVER','won':True,'money':3}}, {'method':'menu','result':{'state':'MENU'}}],{})
        self.assertFalse(d['won']);self.assertEqual(d['terminal_state'],'GAME_OVER')

if __name__=='__main__':unittest.main()
