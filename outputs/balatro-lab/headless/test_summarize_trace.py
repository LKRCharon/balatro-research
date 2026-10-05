import copy
import unittest
from summarize_trace import extract

class TraceAccounting(unittest.TestCase):
    def test_inventory_events_price_purchase_and_pack_return(self):
        joker={'id':1,'key':'j_joker','set':'JOKER','cost':{'buy':4},'rarity':1}
        pack={'id':2,'key':'p_arcana_normal_1','set':'BOOSTER','cost':{'buy':4}}
        shop={'state':'SHOP','ante_num':1,'round_num':1,'money':10,
              'shop':{'cards':[joker]},'packs':{'cards':[pack]}}
        events=[]
        def action(i,method,before,after,params=None,origin=None):
            events.extend([{'event':'intent','id':i,'method':method,'before':before,'params':params or {},'controller_origin':origin},
                           {'event':'result','id':i,'after':after}])
        action(1,'rearrange',shop,shop)
        discounted=copy.deepcopy(shop);discounted['shop']['cards'][0]['cost']['buy']=2
        action(2,'use',shop,discounted)
        action(3,'buy',discounted,{**discounted,'money':8,'shop':{'cards':[]}},{'card':0},'agent')
        opened={'state':'SMODS_BOOSTER_OPENED','ante_num':1,'round_num':1,'money':4,
                'pack':{'cards':[{'id':3,'key':'c_hermit','set':'TAROT'}]}}
        action(4,'buy',discounted,opened,{'pack':0})
        action(5,'pack',opened,discounted,{'card':0})
        action(6,'reroll',discounted,shop)
        out=extract(events)
        self.assertEqual(out['offer_counts_by_area'],{'shop':2,'packs':1,'pack':1})
        self.assertEqual(out['offers'][0]['price_history'],[4,2])
        self.assertEqual(out['observed_shop_joker_rarity_counts'],{'1':2})
        self.assertEqual(out['selection_counts'],{'shop:j_joker':1,'packs:p_arcana_normal_1':1,'pack:c_hermit':1})
        self.assertEqual(out['economy'][2]['net_money_delta'],-2)
        self.assertEqual(out['economy'][2]['controller_origin'],'agent')

    def test_missing_rarity_origin_and_unresolved_intent_stay_unknown(self):
        s={'state':'SHOP','ante_num':1,'round_num':1,'money':5,'shop':{'cards':[{'key':'j_joker','set':'JOKER'}]}}
        events=[{'event':'intent','id':9,'method':'reroll','before':s},
                {'event':'result','id':9,'after':s},
                {'event':'intent','id':10,'method':'buy','before':s,'params':{'card':0}}]
        out=extract(events,[{'action':9,'controller_origin':'agent'}])
        self.assertEqual(out['observed_shop_joker_rarity_counts'],{'unknown':2})
        self.assertEqual(out['unresolved_intents'],1)
        self.assertEqual(out['selection_counts'],{})
        self.assertEqual(out['economy'][0]['controller_origin'],'unknown')

    def test_hybrid_sequence_join_not_gameplay_action_number(self):
        s={'state':'SELECTING_HAND','money':3}
        events=[{'event':'intent','id':12,'method':'play','before':s},
                {'event':'result','id':12,'after':{**s,'money':4}}]
        decisions=[{'action':12,'origin':'manual'}, {'sequence':12,'origin':'controller'}]
        out=extract(events,decisions)
        self.assertEqual(out['economy'][0]['controller_origin'],'controller')
        self.assertEqual(out['economy'][0]['net_money_delta'],1)

    def test_catalog_enrichment_has_provenance_and_observed_precedence(self):
        s={'state':'SHOP','ante_num':1,'round_num':1,'shop':{'cards':[
            {'id':1,'key':'j_joker','set':'JOKER'},
            {'id':2,'key':'j_blueprint','set':'JOKER','rarity':2}]}}
        events=[{'event':'intent','id':1,'before':s}]
        out=extract(events,catalog={'j_joker':{'rarity':1},'j_blueprint':{'rarity':3}})
        self.assertEqual(out['observed_shop_joker_rarity_counts'],{'1':1,'2':1})
        self.assertEqual([o['rarity_source'] for o in out['offers']],['factual_catalog','observed_card'])

if __name__=='__main__':unittest.main()
